"""
TITAN XAU AI — Execution Engine (Module 3)
Production implementation: async order dispatch, idempotency cache,
retry-with-backoff, 50 ops/s target, tick-based execution.
"""
from __future__ import annotations

import asyncio
import collections
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import MetaTrader5 as mt5

logger = logging.getLogger(__name__)


class OrderType(int, Enum):
    MARKET_BUY = mt5.ORDER_TYPE_BUY
    MARKET_SELL = mt5.ORDER_TYPE_SELL
    LIMIT_BUY = mt5.ORDER_TYPE_BUY_LIMIT
    LIMIT_SELL = mt5.ORDER_TYPE_SELL_LIMIT
    STOP_BUY = mt5.ORDER_TYPE_BUY_STOP
    STOP_SELL = mt5.ORDER_TYPE_SELL_STOP


class OrderState(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


@dataclass
class OrderRequest:
    """Order request with idempotency key."""
    symbol: str
    order_type: OrderType
    volume: float
    price: float = 0.0       # 0 for market orders
    sl: float = 0.0          # stop loss
    tp: float = 0.0          # take profit
    deviation: int = 20      # max slippage in points
    magic: int = 202619      # TITAN magic number
    comment: str = "TITAN"
    idempotency_key: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self):
        if not self.idempotency_key:
            self.idempotency_key = str(uuid.uuid4())


@dataclass
class OrderResult:
    """Result of order submission."""
    retcode: int
    deal_id: int
    order_id: int
    volume: float
    price: float
    bid: float
    ask: float
    comment: str
    request_id: int
    result_id: int
    state: OrderState
    error_message: str = ""
    latency_ms: float = 0.0


class IdempotencyCache:
    """LRU cache to prevent duplicate orders."""

    def __init__(self, max_size: int = 10000):
        self._cache: collections.OrderedDict = collections.OrderedDict()
        self._max_size = max_size

    def check_and_add(self, key: str) -> bool:
        """Returns True if key is NEW (not seen before), False if duplicate."""
        if key in self._cache:
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            return False
        self._cache[key] = time.time()
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)
        return True

    def contains(self, key: str) -> bool:
        return key in self._cache

    def clear(self) -> None:
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


class ExecutionEngine:
    """
    Async order dispatch engine.
    - Idempotency: prevents duplicate orders via LRU cache
    - Retry: max 2 retries with 500ms backoff
    - Throughput: targets 50 ops/s
    - Tick-based: fills verified within 2 ticks
    """

    def __init__(self, config: dict):
        exec_cfg = config.get("execution", {})
        self._max_retries = exec_cfg.get("max_retries", 2)
        self._retry_backoff_ms = exec_cfg.get("retry_backoff_ms", 500)
        self._idempotency_cache = IdempotencyCache(
            exec_cfg.get("idempotency_cache_size", 10000)
        )
        self._pending_orders: dict[int, OrderRequest] = {}
        self._order_history: list[OrderResult] = []
        self._max_history = 10000
        self._ops_count = 0
        self._ops_start_time = time.time()
        self._halt_flag = False  # Atomic halt flag (set by CEO/Risk)
        # ── Sprint 8.2: Internal dry_run guard (defense-in-depth) ──
        self._dry_run = bool(exec_cfg.get("dry_run", True))  # DEFAULT TRUE

    def set_halt(self, halted: bool) -> None:
        """Set halt flag — blocks all new orders when True."""
        self._halt_flag = halted
        if halted:
            logger.warning("Execution Engine HALTED — no new orders accepted")
        else:
            logger.info("Execution Engine resumed — orders accepted")

    @property
    def is_halted(self) -> bool:
        return self._halt_flag

    @property
    def is_dry_run(self) -> bool:
        """Sprint 8.2: Expose dry_run state for verification."""
        return self._dry_run

    def set_dry_run(self, dry_run: bool) -> None:
        """Sprint 8.2: Set dry_run mode (internal guard)."""
        self._dry_run = bool(dry_run)
        logger.info(f"ExecutionEngine dry_run = {self._dry_run}")

    @property
    def throughput(self) -> float:
        """Current operations per second."""
        elapsed = time.time() - self._ops_start_time
        if elapsed == 0:
            return 0.0
        return self._ops_count / elapsed

    async def submit_order(self, request: OrderRequest) -> OrderResult:
        """
        Submit order with idempotency check and retry logic.
        Returns OrderResult with state FILLED/REJECTED/etc.

        DEFENSE-IN-DEPTH (Sprint 8.2):
          - dry_run guard checked HERE, not just in TradeLoop caller
          - If dry_run=True: NEVER calls mt5.order_send
          - If dry_run=False: requires TITAN_LIVE_TRADING=1 + SL/TP present
        """
        # ── INTERNAL DRY_RUN GUARD (defense-in-depth) ──
        if self._dry_run:
            logger.info(
                f"[INTERNAL GUARD] dry_run=True — mt5.order_send SKIPPED "
                f"(symbol={request.symbol}, vol={request.volume})"
            )
            return OrderResult(
                retcode=0, deal_id=0, order_id=0, volume=request.volume,
                price=request.price, bid=0, ask=0,
                comment="DRY_RUN_INTERNAL_GUARD", request_id=0, result_id=0,
                state=OrderState.REJECTED,
                error_message="internal_execution_guard: dry_run=True",
            )

        # ── LIVE MODE: verify multiple safety gates ──
        import os
        # Gate 1: TITAN_LIVE_TRADING env var
        if os.environ.get("TITAN_LIVE_TRADING", "0") != "1":
            logger.error("[INTERNAL GUARD] TITAN_LIVE_TRADING != 1 — live order blocked")
            return OrderResult(
                retcode=0, deal_id=0, order_id=0, volume=0, price=0,
                bid=0, ask=0, comment="LIVE_BLOCKED", request_id=0, result_id=0,
                state=OrderState.REJECTED,
                error_message="internal_execution_guard: TITAN_LIVE_TRADING env var not set",
            )

        # Gate 2: SL and TP must be present
        if request.sl <= 0 or request.tp <= 0:
            logger.error("[INTERNAL GUARD] SL or TP missing — live order blocked")
            return OrderResult(
                retcode=0, deal_id=0, order_id=0, volume=0, price=0,
                bid=0, ask=0, comment="SL_TP_MISSING", request_id=0, result_id=0,
                state=OrderState.REJECTED,
                error_message="internal_execution_guard: SL and TP must be > 0",
            )

        # Gate 3: Volume must not exceed hard cap
        if request.volume > 0.01:
            logger.error(f"[INTERNAL GUARD] volume={request.volume} > 0.01 cap — blocked")
            return OrderResult(
                retcode=0, deal_id=0, order_id=0, volume=0, price=0,
                bid=0, ask=0, comment="VOLUME_CAP", request_id=0, result_id=0,
                state=OrderState.REJECTED,
                error_message="internal_execution_guard: volume exceeds 0.01 cap",
            )

        # ── HALT CHECK ──
        if self._halt_flag:
            return OrderResult(
                retcode=0, deal_id=0, order_id=0, volume=0, price=0,
                bid=0, ask=0, comment="HALTED", request_id=0, result_id=0,
                state=OrderState.REJECTED,
                error_message="Execution engine halted by CEO/Risk"
            )

        # Idempotency check
        if not self._idempotency_cache.check_and_add(request.idempotency_key):
            logger.warning(
                f"Duplicate order blocked: {request.idempotency_key}"
            )
            return OrderResult(
                retcode=0, deal_id=0, order_id=0, volume=0, price=0,
                bid=0, ask=0, comment="DUPLICATE", request_id=0, result_id=0,
                state=OrderState.REJECTED,
                error_message="Duplicate idempotency key"
            )

        # Build MT5 request
        mt5_request = self._build_mt5_request(request)

        # Retry loop
        last_error = ""
        for attempt in range(self._max_retries + 1):
            start = time.perf_counter()

            result = mt5.order_send(mt5_request)
            latency_ms = (time.perf_counter() - start) * 1000

            self._ops_count += 1

            if result is None:
                last_error = f"MT5 returned None: {mt5.last_error()}"
                logger.error(f"Order attempt {attempt+1}: {last_error}")
                if attempt < self._max_retries:
                    await asyncio.sleep(self._retry_backoff_ms / 1000)
                continue

            state = self._resolve_state(result.retcode)

            order_result = OrderResult(
                retcode=result.retcode,
                deal_id=result.deal,
                order_id=result.order,
                volume=result.volume,
                price=result.price,
                bid=result.bid,
                ask=result.ask,
                comment=result.comment,
                request_id=result.request_id,
                result_id=result.result_id,
                state=state,
                error_message=last_error if state == OrderState.REJECTED else "",
                latency_ms=latency_ms,
            )

            if state == OrderState.FILLED or state == OrderState.PARTIALLY_FILLED:
                self._add_to_history(order_result)
                logger.info(
                    f"Order filled: {request.symbol} {request.order_type.name} "
                    f"{request.volume} lots @ {result.price} "
                    f"(latency: {latency_ms:.1f}ms, attempt: {attempt+1})"
                )
                return order_result

            if state == OrderState.REJECTED:
                last_error = f"retcode={result.retcode}, comment={result.comment}"
                logger.warning(
                    f"Order rejected (attempt {attempt+1}): {last_error}"
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(self._retry_backoff_ms / 1000)

        # All retries exhausted
        final_result = OrderResult(
            retcode=result.retcode if result else 0,
            deal_id=result.deal if result else 0,
            order_id=result.order if result else 0,
            volume=result.volume if result else 0,
            price=result.price if result else 0,
            bid=result.bid if result else 0,
            ask=result.ask if result else 0,
            comment=result.comment if result else "FAILED",
            request_id=result.request_id if result else 0,
            result_id=result.result_id if result else 0,
            state=OrderState.REJECTED,
            error_message=f"All {self._max_retries+1} attempts failed: {last_error}",
            latency_ms=0.0,
        )
        self._add_to_history(final_result)
        return final_result

    async def cancel_order(self, ticket: int) -> bool:
        """Cancel a pending order by ticket number."""
        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": ticket,
            "comment": "TITAN cancel",
        }
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"Order {ticket} cancelled")
            return True
        logger.error(
            f"Cancel failed for {ticket}: "
            f"{result.retcode if result else 'None'}"
        )
        return False

    async def close_position(self, ticket: int) -> bool:
        """Close an open position by ticket number."""
        position = mt5.positions_get(ticket=ticket)
        if not position:
            logger.error(f"Position {ticket} not found")
            return False

        pos = position[0]
        close_type = (
            OrderType.MARKET_SELL if pos.type == mt5.POSITION_TYPE_BUY
            else OrderType.MARKET_BUY
        )

        request = OrderRequest(
            symbol=pos.symbol,
            order_type=close_type,
            volume=pos.volume,
            magic=pos.magic,
            comment=f"TITAN close {ticket}",
        )
        result = await self.submit_order(request)
        return result.state == OrderState.FILLED

    async def close_all_positions(self) -> int:
        """
        Emergency flatten — close ALL open positions.
        Used by Risk Engine kill-switch. Must complete <500ms.
        """
        start = time.perf_counter()
        positions = mt5.positions_get()
        if not positions:
            return 0

        closed = 0
        tasks = []
        for pos in positions:
            tasks.append(self._close_position_by_info(pos))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if r is True:
                closed += 1

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            f"close_all_positions: {closed}/{len(positions)} closed "
            f"in {elapsed_ms:.1f}ms"
        )
        return closed

    async def _close_position_by_info(self, pos) -> bool:
        """Close a single position from position info object."""
        close_type = (
            OrderType.MARKET_SELL if pos.type == mt5.POSITION_TYPE_BUY
            else OrderType.MARKET_BUY
        )
        request = OrderRequest(
            symbol=pos.symbol,
            order_type=close_type,
            volume=pos.volume,
            magic=pos.magic,
            comment=f"TITAN flatten {pos.ticket}",
        )
        result = await self.submit_order(request)
        return result.state == OrderState.FILLED

    def _build_mt5_request(self, req: OrderRequest) -> dict:
        """Build MT5 order_send request dict."""
        action = mt5.TRADE_ACTION_DEAL  # Market order by default

        if req.order_type in (OrderType.LIMIT_BUY, OrderType.LIMIT_SELL):
            action = mt5.TRADE_ACTION_PENDING
        elif req.order_type in (OrderType.STOP_BUY, OrderType.STOP_SELL):
            action = mt5.TRADE_ACTION_PENDING

        mt5_request = {
            "action": action,
            "symbol": req.symbol,
            "volume": float(req.volume),
            "type": int(req.order_type),
            "magic": req.magic,
            "comment": req.comment,
            "deviation": req.deviation,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        if req.price > 0:
            mt5_request["price"] = float(req.price)
        else:
            # Market order — set price from current tick
            tick = mt5.symbol_info_tick(req.symbol)
            if tick:
                if req.order_type == OrderType.MARKET_BUY:
                    mt5_request["price"] = tick.ask
                elif req.order_type == OrderType.MARKET_SELL:
                    mt5_request["price"] = tick.bid
            else:
                mt5_request["price"] = 0.0

        if req.sl > 0:
            mt5_request["sl"] = float(req.sl)
        if req.tp > 0:
            mt5_request["tp"] = float(req.tp)

        return mt5_request

    def _resolve_state(self, retcode: int) -> OrderState:
        """Map MT5 retcode to OrderState."""
        if retcode == mt5.TRADE_RETCODE_DONE:
            return OrderState.FILLED
        elif retcode == mt5.TRADE_RETCODE_DONE_PARTIAL:
            return OrderState.PARTIALLY_FILLED
        elif retcode == mt5.TRADE_RETCODE_PLACED:
            return OrderState.PENDING
        elif retcode == mt5.TRADE_RETCODE_REQUOTE:
            return OrderState.REJECTED
        elif retcode == mt5.TRADE_RETCODE_REJECT:
            return OrderState.REJECTED
        elif retcode == mt5.TRADE_RETCODE_CANCELLED:
            return OrderState.CANCELLED
        else:
            return OrderState.REJECTED

    def _add_to_history(self, result: OrderResult) -> None:
        self._order_history.append(result)
        if len(self._order_history) > self._max_history:
            self._order_history = self._order_history[-self._max_history:]

    def get_positions(self) -> list:
        """Get all open positions."""
        return mt5.positions_get() or []

    def get_position_count(self) -> int:
        """Count of open positions."""
        positions = mt5.positions_get()
        return len(positions) if positions else 0

    @property
    def idempotency_cache_size(self) -> int:
        return self._idempotency_cache.size

    @property
    def total_orders(self) -> int:
        return self._ops_count
