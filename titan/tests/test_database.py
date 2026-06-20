"""Tests for Database Layer"""
import pytest
import asyncio
import os
import tempfile
from titan.database.layer import (
    Database, TradeRepository, OrderRepository, PositionRepository,
    StateRepository, MetricsRepository, RedisCache, SCHEMA_SQL,
)


@pytest.fixture
async def db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        database = Database(db_path)
        await database.initialize()
        yield database
        await database.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


class TestDatabase:
    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, db):
        tables = await db.query_all(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        table_names = [t["name"] for t in tables]
        assert "trades" in table_names
        assert "orders" in table_names
        assert "positions" in table_names
        assert "ceo_state" in table_names
        assert "weighting_state" in table_names
        assert "risk_state" in table_names
        assert "metrics" in table_names

    @pytest.mark.asyncio
    async def test_execute_and_query(self, db):
        await db.execute(
            "INSERT INTO metrics (timestamp, metric_name, metric_value) VALUES (?, ?, ?)",
            (1234567890, "test_metric", 42.0)
        )
        row = await db.query_one("SELECT * FROM metrics WHERE metric_name=?", ("test_metric",))
        assert row is not None
        assert row["metric_value"] == 42.0


class TestTradeRepository:
    @pytest.mark.asyncio
    async def test_save_and_retrieve_trade(self, db):
        repo = TradeRepository(db)
        trade_id = await repo.save_trade({
            "ticket": 12345, "symbol": "XAUUSD", "direction": 1,
            "volume": 0.5, "entry_price": 2000.0, "stop_loss": 1990.0,
            "take_profit": 2020.0, "model_id": "xgboost", "strategy": "trend",
            "regime": "TREND",
        })
        assert trade_id > 0

        open_trades = await repo.get_open_trades()
        assert len(open_trades) == 1
        assert open_trades[0]["symbol"] == "XAUUSD"

    @pytest.mark.asyncio
    async def test_close_trade(self, db):
        repo = TradeRepository(db)
        trade_id = await repo.save_trade({
            "symbol": "XAUUSD", "direction": 1, "volume": 0.1,
            "entry_price": 2000.0,
        })
        await repo.close_trade(trade_id, 2010.0, 100.0)

        open_trades = await repo.get_open_trades()
        assert len(open_trades) == 0

        history = await repo.get_trade_history()
        assert len(history) == 1
        assert history[0]["status"] == "CLOSED"
        assert history[0]["pnl"] == 100.0


class TestOrderRepository:
    @pytest.mark.asyncio
    async def test_save_order(self, db):
        repo = OrderRepository(db)
        order_id = await repo.save_order({
            "idempotency_key": "test-key-001", "symbol": "XAUUSD",
            "order_type": "MARKET_BUY", "volume": 0.5, "price": 2000.0,
            "sl": 1990.0, "tp": 2020.0, "retcode": 10009,
            "deal_id": 123, "order_ticket": 456, "state": "FILLED",
            "latency_ms": 15.5,
        })
        assert order_id > 0

    @pytest.mark.asyncio
    async def test_order_exists(self, db):
        repo = OrderRepository(db)
        await repo.save_order({
            "idempotency_key": "unique-key", "symbol": "XAUUSD",
            "order_type": "MARKET_BUY", "volume": 0.1,
        })
        assert await repo.order_exists("unique-key") is True
        assert await repo.order_exists("nonexistent") is False

    @pytest.mark.asyncio
    async def test_duplicate_key_ignored(self, db):
        repo = OrderRepository(db)
        await repo.save_order({
            "idempotency_key": "dup-key", "symbol": "XAUUSD",
            "order_type": "MARKET_BUY", "volume": 0.1,
        })
        # Second insert with same key should be ignored (INSERT OR IGNORE)
        await repo.save_order({
            "idempotency_key": "dup-key", "symbol": "XAUUSD",
            "order_type": "MARKET_BUY", "volume": 0.2,
        })
        orders = await db.query_all("SELECT * FROM orders WHERE idempotency_key=?", ("dup-key",))
        assert len(orders) == 1  # Only first insert


class TestPositionRepository:
    @pytest.mark.asyncio
    async def test_upsert_position(self, db):
        repo = PositionRepository(db)
        await repo.upsert_position({
            "ticket": 1001, "symbol": "XAUUSD", "direction": 1,
            "volume": 0.5, "entry_price": 2000.0,
        })
        positions = await repo.get_all_positions()
        assert len(positions) == 1
        assert positions[0]["ticket"] == 1001

        # Upsert (update existing)
        await repo.upsert_position({
            "ticket": 1001, "symbol": "XAUUSD", "direction": 1,
            "volume": 0.5, "entry_price": 2000.0, "current_price": 2010.0,
            "floating_pnl": 500.0,
        })
        positions = await repo.get_all_positions()
        assert len(positions) == 1  # Still 1 (not duplicated)
        assert positions[0]["current_price"] == 2010.0

    @pytest.mark.asyncio
    async def test_delete_position(self, db):
        repo = PositionRepository(db)
        await repo.upsert_position({
            "ticket": 2002, "symbol": "XAUUSD", "direction": -1,
            "volume": 0.3, "entry_price": 2000.0,
        })
        await repo.delete_position(2002)
        assert await repo.get_position_count() == 0


class TestStateRepository:
    @pytest.mark.asyncio
    async def test_save_and_get_ceo_state(self, db):
        repo = StateRepository(db)
        await repo.save_ceo_state("GREEN", 95.5, {"xgb": 96, "lstm": 93},
                                  94.0, 92.0, 88.0, 42)
        state = await repo.get_latest_ceo_state()
        assert state is not None
        assert state["system_status"] == "GREEN"
        assert state["overall_health"] == 95.5
        assert state["cycle_count"] == 42

    @pytest.mark.asyncio
    async def test_save_and_get_weighting_state(self, db):
        repo = StateRepository(db)
        await repo.save_weighting_state(
            "mab_thompson", "trend",
            {"xgboost": 0.25, "lstm": 0.35, "transformer": 0.30, "rl_manager": 0.10},
            15
        )
        state = await repo.get_latest_weighting_state()
        assert state is not None
        assert state["algorithm_used"] == "mab_thompson"
        assert state["regime"] == "trend"

    @pytest.mark.asyncio
    async def test_save_and_get_risk_state(self, db):
        repo = StateRepository(db)
        await repo.save_risk_state("NORMAL", 10000, 10000, 2.5, 1.0, 0.2, False, 5, 50)
        state = await repo.get_latest_risk_state()
        assert state is not None
        assert state["mode"] == "NORMAL"
        assert state["kill_switch_armed"] == 0


class TestMetricsRepository:
    @pytest.mark.asyncio
    async def test_save_and_get_metric(self, db):
        repo = MetricsRepository(db)
        await repo.save_metric("sharpe", 2.14, {"strategy": "trend"})
        await repo.save_metric("sharpe", 2.28, {"strategy": "trend"})
        metrics = await repo.get_metrics("sharpe")
        assert len(metrics) == 2
        assert metrics[0]["metric_value"] == 2.28  # Most recent first


class TestRedisCache:
    @pytest.mark.asyncio
    async def test_degrades_gracefully(self):
        """Redis should degrade to no-op if unavailable."""
        cache = RedisCache(host="localhost", port=12345)  # Wrong port
        connected = await cache.connect()
        assert connected is False
        assert cache.connected is False

        # Operations should be no-ops, not crashes
        await cache.set("key", "value")
        result = await cache.get("key")
        assert result is None
