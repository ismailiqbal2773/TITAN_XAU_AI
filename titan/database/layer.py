"""
TITAN XAU AI — Database Layer
SQLite persistence + Redis caching. Repository pattern.
Connection pooling. Schema migrations. State persistence.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

import aiosqlite

logger = logging.getLogger(__name__)

# ─── Schema DDL ───

SCHEMA_SQL = """
-- Trades
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket INTEGER,
    symbol TEXT NOT NULL,
    direction INTEGER NOT NULL,    -- +1 long, -1 short
    volume REAL NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    stop_loss REAL,
    take_profit REAL,
    pnl REAL DEFAULT 0,
    pnl_pips REAL DEFAULT 0,
    model_id TEXT,
    strategy TEXT,
    regime TEXT,
    opened_at REAL NOT NULL,
    closed_at REAL,
    status TEXT DEFAULT 'OPEN'    -- OPEN / CLOSED / CANCELLED
);

-- Orders
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT UNIQUE NOT NULL,
    symbol TEXT NOT NULL,
    order_type TEXT NOT NULL,
    volume REAL NOT NULL,
    price REAL,
    sl REAL,
    tp REAL,
    retcode INTEGER,
    deal_id INTEGER,
    order_ticket INTEGER,
    state TEXT,                    -- FILLED / REJECTED / CANCELLED
    latency_ms REAL,
    created_at REAL NOT NULL
);

-- Positions (snapshot of current open positions)
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket INTEGER UNIQUE NOT NULL,
    symbol TEXT NOT NULL,
    direction INTEGER NOT NULL,
    volume REAL NOT NULL,
    entry_price REAL NOT NULL,
    current_price REAL,
    stop_loss REAL,
    take_profit REAL,
    floating_pnl REAL DEFAULT 0,
    swap REAL DEFAULT 0,
    model_id TEXT,
    opened_at REAL NOT NULL,
    updated_at REAL
);

-- CEO State (latest snapshot)
CREATE TABLE IF NOT EXISTS ceo_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    system_status TEXT NOT NULL,   -- GREEN / YELLOW / RED / RED_PRESERVE
    overall_health REAL,
    model_health_json TEXT,        -- JSON dict
    execution_quality REAL,
    risk_score REAL,
    regime_confidence REAL,
    cycle_count INTEGER
);

-- Weighting State
CREATE TABLE IF NOT EXISTS weighting_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    algorithm_used TEXT NOT NULL,
    regime TEXT NOT NULL,
    weights_json TEXT NOT NULL,    -- JSON dict
    cycle_count INTEGER
);

-- Risk State
CREATE TABLE IF NOT EXISTS risk_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    mode TEXT NOT NULL,            -- NORMAL / DEFGRESSIVE / EMERGENCY
    equity REAL,
    balance REAL,
    max_drawdown_pct REAL,
    daily_drawdown_pct REAL,
    risk_utilization REAL,
    kill_switch_armed INTEGER DEFAULT 0,
    veto_count INTEGER DEFAULT 0,
    allow_count INTEGER DEFAULT 0
);

-- Metrics (time-series)
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    tags_json TEXT                  -- JSON dict of tags
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_opened ON trades(opened_at);
CREATE INDEX IF NOT EXISTS idx_orders_idem ON orders(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_positions_ticket ON positions(ticket);
CREATE INDEX IF NOT EXISTS idx_ceo_ts ON ceo_state(timestamp);
CREATE INDEX IF NOT EXISTS idx_weighting_ts ON weighting_state(timestamp);
CREATE INDEX IF NOT EXISTS idx_risk_ts ON risk_state(timestamp);
CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(metric_name);
"""


class Database:
    """Async SQLite database with connection pooling."""

    def __init__(self, db_path: str = "data/titan.db"):
        self._db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize database — create dirs, connect, run migrations."""
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA_SQL)
        await self._conn.commit()
        logger.info(f"Database initialized: {self._db_path}")

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("Database closed")

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._conn

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        async with self._lock:
            cursor = await self._conn.execute(sql, params)
            await self._conn.commit()
            return cursor

    async def executemany(self, sql: str, params_list: list[tuple]) -> None:
        async with self._lock:
            await self._conn.executemany(sql, params_list)
            await self._conn.commit()

    async def query_one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        async with self._lock:
            cursor = await self._conn.execute(sql, params)
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def query_all(self, sql: str, params: tuple = ()) -> list[dict]:
        async with self._lock:
            cursor = await self._conn.execute(sql, params)
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


# ─── Repository Pattern ───

class TradeRepository:
    def __init__(self, db: Database):
        self._db = db

    async def save_trade(self, trade: dict) -> int:
        cursor = await self._db.execute(
            """INSERT INTO trades (ticket, symbol, direction, volume, entry_price,
               exit_price, stop_loss, take_profit, pnl, pnl_pips, model_id,
               strategy, regime, opened_at, closed_at, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (trade.get("ticket"), trade["symbol"], trade["direction"],
             trade["volume"], trade["entry_price"], trade.get("exit_price"),
             trade.get("stop_loss"), trade.get("take_profit"),
             trade.get("pnl", 0), trade.get("pnl_pips", 0),
             trade.get("model_id"), trade.get("strategy"), trade.get("regime"),
             trade.get("opened_at", time.time()), trade.get("closed_at"),
             trade.get("status", "OPEN"))
        )
        return cursor.lastrowid

    async def close_trade(self, trade_id: int, exit_price: float, pnl: float) -> None:
        await self._db.execute(
            "UPDATE trades SET exit_price=?, pnl=?, status='CLOSED', closed_at=? WHERE id=?",
            (exit_price, pnl, time.time(), trade_id)
        )

    async def get_open_trades(self) -> list[dict]:
        return await self._db.query_all(
            "SELECT * FROM trades WHERE status='OPEN' ORDER BY opened_at DESC"
        )

    async def get_trade_history(self, limit: int = 100) -> list[dict]:
        return await self._db.query_all(
            "SELECT * FROM trades WHERE status='CLOSED' ORDER BY closed_at DESC LIMIT ?",
            (limit,)
        )


class OrderRepository:
    def __init__(self, db: Database):
        self._db = db

    async def save_order(self, order: dict) -> int:
        cursor = await self._db.execute(
            """INSERT OR IGNORE INTO orders (idempotency_key, symbol, order_type,
               volume, price, sl, tp, retcode, deal_id, order_ticket, state,
               latency_ms, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (order["idempotency_key"], order["symbol"], order["order_type"],
             order["volume"], order.get("price"), order.get("sl"), order.get("tp"),
             order.get("retcode"), order.get("deal_id"), order.get("order_ticket"),
             order.get("state"), order.get("latency_ms"), time.time())
        )
        return cursor.lastrowid

    async def order_exists(self, idempotency_key: str) -> bool:
        row = await self._db.query_one(
            "SELECT 1 FROM orders WHERE idempotency_key=?", (idempotency_key,)
        )
        return row is not None


class PositionRepository:
    def __init__(self, db: Database):
        self._db = db

    async def upsert_position(self, pos: dict) -> None:
        await self._db.execute(
            """INSERT OR REPLACE INTO positions (ticket, symbol, direction, volume,
               entry_price, current_price, stop_loss, take_profit, floating_pnl,
               swap, model_id, opened_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pos["ticket"], pos["symbol"], pos["direction"], pos["volume"],
             pos["entry_price"], pos.get("current_price"), pos.get("stop_loss"),
             pos.get("take_profit"), pos.get("floating_pnl", 0), pos.get("swap", 0),
             pos.get("model_id"), pos.get("opened_at", time.time()), time.time())
        )

    async def delete_position(self, ticket: int) -> None:
        await self._db.execute("DELETE FROM positions WHERE ticket=?", (ticket,))

    async def get_all_positions(self) -> list[dict]:
        return await self._db.query_all("SELECT * FROM positions ORDER BY opened_at")

    async def get_position_count(self) -> int:
        row = await self._db.query_one("SELECT COUNT(*) as cnt FROM positions")
        return row["cnt"] if row else 0


class StateRepository:
    """Persists CEO, Weighting, and Risk state snapshots."""

    def __init__(self, db: Database):
        self._db = db

    async def save_ceo_state(self, status: str, overall: float,
                             model_health: dict, eqs: float, risk: float,
                             regime_conf: float, cycle: int) -> None:
        await self._db.execute(
            """INSERT INTO ceo_state (timestamp, system_status, overall_health,
               model_health_json, execution_quality, risk_score, regime_confidence, cycle_count)
               VALUES (?,?,?,?,?,?,?,?)""",
            (time.time(), status, overall, json.dumps(model_health),
             eqs, risk, regime_conf, cycle)
        )

    async def get_latest_ceo_state(self) -> Optional[dict]:
        return await self._db.query_one(
            "SELECT * FROM ceo_state ORDER BY timestamp DESC LIMIT 1"
        )

    async def save_weighting_state(self, algorithm: str, regime: str,
                                   weights: dict, cycle: int) -> None:
        await self._db.execute(
            """INSERT INTO weighting_state (timestamp, algorithm_used, regime, weights_json, cycle_count)
               VALUES (?,?,?,?,?)""",
            (time.time(), algorithm, regime, json.dumps(weights), cycle)
        )

    async def get_latest_weighting_state(self) -> Optional[dict]:
        return await self._db.query_one(
            "SELECT * FROM weighting_state ORDER BY timestamp DESC LIMIT 1"
        )

    async def save_risk_state(self, mode: str, equity: float, balance: float,
                              max_dd: float, daily_dd: float, risk_util: float,
                              kill_switch: bool, vetoes: int, allows: int) -> None:
        await self._db.execute(
            """INSERT INTO risk_state (timestamp, mode, equity, balance,
               max_drawdown_pct, daily_drawdown_pct, risk_utilization,
               kill_switch_armed, veto_count, allow_count)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (time.time(), mode, equity, balance, max_dd, daily_dd,
             risk_util, int(kill_switch), vetoes, allows)
        )

    async def get_latest_risk_state(self) -> Optional[dict]:
        return await self._db.query_one(
            "SELECT * FROM risk_state ORDER BY timestamp DESC LIMIT 1"
        )


class MetricsRepository:
    def __init__(self, db: Database):
        self._db = db

    async def save_metric(self, name: str, value: float, tags: dict = None) -> None:
        await self._db.execute(
            "INSERT INTO metrics (timestamp, metric_name, metric_value, tags_json) VALUES (?,?,?,?)",
            (time.time(), name, value, json.dumps(tags) if tags else None)
        )

    async def get_metrics(self, name: str, limit: int = 100) -> list[dict]:
        return await self._db.query_all(
            "SELECT * FROM metrics WHERE metric_name=? ORDER BY timestamp DESC LIMIT ?",
            (name, limit)
        )


# ─── Redis Cache (optional, degrades gracefully) ───

class RedisCache:
    """Redis cache for hot data. Degrades to no-op if Redis unavailable."""

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self._host = host
        self._port = port
        self._db = db
        self._redis = None
        self._connected = False

    async def connect(self) -> bool:
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.Redis(
                host=self._host, port=self._port, db=self._db,
                decode_responses=True, socket_timeout=2,
            )
            await self._redis.ping()
            self._connected = True
            logger.info(f"Redis connected: {self._host}:{self._port}")
            return True
        except Exception as e:
            logger.warning(f"Redis unavailable (degrading to no-op): {e}")
            self._connected = False
            return False

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()
            self._connected = False

    async def set(self, key: str, value: str, ttl: int = 60) -> None:
        if not self._connected:
            return
        try:
            await self._redis.set(key, value, ex=ttl)
        except Exception:
            pass  # Silent degradation

    async def get(self, key: str) -> Optional[str]:
        if not self._connected:
            return None
        try:
            return await self._redis.get(key)
        except Exception:
            return None

    async def set_json(self, key: str, value: Any, ttl: int = 60) -> None:
        await self.set(key, json.dumps(value), ttl)

    async def get_json(self, key: str) -> Any:
        val = await self.get(key)
        return json.loads(val) if val else None

    @property
    def connected(self) -> bool:
        return self._connected
