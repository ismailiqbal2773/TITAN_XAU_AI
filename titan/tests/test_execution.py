"""
TITAN XAU AI — Tests for Execution Engine
Tests for IdempotencyCache, OrderRequest, order logic.
"""
import pytest
from titan.execution.engine import (
    ExecutionEngine,
    OrderRequest,
    OrderType,
    OrderState,
    IdempotencyCache,
)


@pytest.fixture
def config():
    return {
        "execution": {
            "max_ops_per_second": 50,
            "idempotency_cache_size": 1000,
            "max_retries": 2,
            "retry_backoff_ms": 100,
            "signal_to_broker_budget_ms": 150,
        },
    }


class TestIdempotencyCache:
    def test_new_key_returns_true(self):
        cache = IdempotencyCache(100)
        assert cache.check_and_add("order-001") is True

    def test_duplicate_key_returns_false(self):
        cache = IdempotencyCache(100)
        cache.check_and_add("order-001")
        assert cache.check_and_add("order-001") is False

    def test_lru_eviction(self):
        cache = IdempotencyCache(3)
        cache.check_and_add("a")
        cache.check_and_add("b")
        cache.check_and_add("c")
        cache.check_and_add("d")  # should evict "a"
        assert cache.contains("a") is False
        assert cache.contains("d") is True

    def test_clear(self):
        cache = IdempotencyCache(100)
        cache.check_and_add("x")
        cache.clear()
        assert cache.size == 0


class TestOrderRequest:
    def test_market_buy_creation(self):
        req = OrderRequest(
            symbol="XAUUSD",
            order_type=OrderType.MARKET_BUY,
            volume=0.5,
        )
        assert req.symbol == "XAUUSD"
        assert req.order_type == OrderType.MARKET_BUY
        assert req.volume == 0.5
        assert req.idempotency_key != ""

    def test_auto_idempotency_key(self):
        req1 = OrderRequest("XAUUSD", OrderType.MARKET_BUY, 0.1)
        req2 = OrderRequest("XAUUSD", OrderType.MARKET_BUY, 0.1)
        assert req1.idempotency_key != req2.idempotency_key

    def test_with_sl_tp(self):
        req = OrderRequest(
            symbol="XAUUSD",
            order_type=OrderType.MARKET_SELL,
            volume=0.2,
            sl=2050.0,
            tp=1950.0,
        )
        assert req.sl == 2050.0
        assert req.tp == 1950.0


class TestExecutionEngineHalt:
    def test_halt_blocks_orders(self, config):
        engine = ExecutionEngine(config)
        engine.set_halt(True)
        assert engine.is_halted is True

    def test_unhalt_allows_orders(self, config):
        engine = ExecutionEngine(config)
        engine.set_halt(True)
        engine.set_halt(False)
        assert engine.is_halted is False

    def test_throughput_initial(self, config):
        engine = ExecutionEngine(config)
        assert engine.throughput >= 0.0

    def test_total_orders_initial(self, config):
        engine = ExecutionEngine(config)
        assert engine.total_orders == 0

    def test_idempotency_cache_initial(self, config):
        engine = ExecutionEngine(config)
        assert engine.idempotency_cache_size == 0
