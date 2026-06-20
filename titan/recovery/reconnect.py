"""
TITAN Auto-Reconnect Wrappers
===============================
Wraps existing DB / Redis / MT5 connections with auto-reconnect logic.

Design: do NOT modify existing classes. Instead, provide thin wrapper
classes that intercept calls and retry on connection failure with
exponential backoff.

ReconnectPolicy:
    max_retries:       10
    base_delay_ms:     100
    max_delay_ms:      5000
    backoff_factor:    2.0
    jitter:            True (±25% randomization to avoid thundering herd)
"""
from __future__ import annotations
import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Optional, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class ReconnectPolicy:
    max_retries: int = 10
    base_delay_ms: int = 100
    max_delay_ms: int = 5000
    backoff_factor: float = 2.0
    jitter: bool = True

    def delay_for(self, attempt: int) -> float:
        """Compute delay (seconds) for given attempt number (0-indexed)."""
        delay_ms = min(
            self.base_delay_ms * (self.backoff_factor ** attempt),
            self.max_delay_ms,
        )
        if self.jitter:
            delay_ms *= random.uniform(0.75, 1.25)
        return delay_ms / 1000.0


class AutoReconnectDB:
    """Wraps titan.database.layer.Database with auto-reconnect."""

    def __init__(self, db, policy: ReconnectPolicy | None = None,
                 on_event: Callable[[str, dict], Awaitable[None]] | None = None):
        self._db = db
        self._policy = policy or ReconnectPolicy()
        self._on_event = on_event
        self._reconnect_count = 0
        self._last_error: str | None = None

    @property
    def underlying(self):
        return self._db

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    async def _try_reconnect(self) -> bool:
        """Attempt to reconnect. Returns True on success."""
        for attempt in range(self._policy.max_retries):
            try:
                if self._on_event:
                    await self._on_event("reconnect_attempt",
                                          {"component": "db", "attempt": attempt + 1})
                # Close stale conn if any
                if self._db._conn is not None:
                    try:
                        await self._db._conn.close()
                    except Exception:
                        pass
                    self._db._conn = None
                # Re-init
                await self._db.initialize()
                self._reconnect_count += 1
                self._last_error = None
                if self._on_event:
                    await self._on_event("reconnect_success",
                                          {"component": "db", "attempt": attempt + 1})
                logger.info(f"DB reconnect succeeded on attempt {attempt + 1}")
                return True
            except Exception as e:
                self._last_error = str(e)
                delay = self._policy.delay_for(attempt)
                logger.warning(f"DB reconnect attempt {attempt + 1} failed: {e}. "
                                f"Retrying in {delay:.2f}s")
                if self._on_event:
                    await self._on_event("reconnect_failed",
                                          {"component": "db", "attempt": attempt + 1,
                                           "error": str(e)[:100]})
                await asyncio.sleep(delay)
        logger.error(f"DB reconnect failed after {self._policy.max_retries} attempts")
        return False

    async def execute(self, sql: str, params: tuple = ()):
        try:
            return await self._db.execute(sql, params)
        except Exception as e:
            logger.warning(f"DB execute failed: {e}. Attempting reconnect...")
            if await self._try_reconnect():
                return await self._db.execute(sql, params)
            raise

    async def query_one(self, sql: str, params: tuple = ()):
        try:
            return await self._db.query_one(sql, params)
        except Exception as e:
            logger.warning(f"DB query_one failed: {e}. Attempting reconnect...")
            if await self._try_reconnect():
                return await self._db.query_one(sql, params)
            raise

    async def query_all(self, sql: str, params: tuple = ()):
        try:
            return await self._db.query_all(sql, params)
        except Exception as e:
            logger.warning(f"DB query_all failed: {e}. Attempting reconnect...")
            if await self._try_reconnect():
                return await self._db.query_all(sql, params)
            raise

    @property
    def conn(self):
        return self._db.conn


class AutoReconnectRedis:
    """Wraps titan.database.layer.RedisCache with auto-reconnect."""

    def __init__(self, redis, policy: ReconnectPolicy | None = None,
                 on_event: Callable[[str, dict], Awaitable[None]] | None = None):
        self._redis = redis
        self._policy = policy or ReconnectPolicy()
        self._on_event = on_event
        self._reconnect_count = 0

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    async def _try_reconnect(self) -> bool:
        for attempt in range(self._policy.max_retries):
            try:
                if self._on_event:
                    await self._on_event("reconnect_attempt",
                                          {"component": "redis", "attempt": attempt + 1})
                await self._redis.close()
                await self._redis.connect()
                if self._redis.connected:
                    self._reconnect_count += 1
                    if self._on_event:
                        await self._on_event("reconnect_success",
                                              {"component": "redis", "attempt": attempt + 1})
                    logger.info(f"Redis reconnect succeeded on attempt {attempt + 1}")
                    return True
            except Exception as e:
                delay = self._policy.delay_for(attempt)
                logger.warning(f"Redis reconnect attempt {attempt + 1} failed: {e}. "
                                f"Retrying in {delay:.2f}s")
                if self._on_event:
                    await self._on_event("reconnect_failed",
                                          {"component": "redis", "attempt": attempt + 1,
                                           "error": str(e)[:100]})
                await asyncio.sleep(delay)
        return False

    async def get(self, key: str):
        if not self._redis.connected:
            await self._try_reconnect()
        if not self._redis.connected:
            return None  # graceful degrade
        try:
            return await self._redis.get(key)
        except Exception as e:
            logger.warning(f"Redis get failed: {e}. Attempting reconnect...")
            if await self._try_reconnect():
                return await self._redis.get(key)
            return None  # degrade

    async def set(self, key: str, value: str, ttl: int = 60) -> None:
        if not self._redis.connected:
            await self._try_reconnect()
        if not self._redis.connected:
            return  # degrade
        try:
            await self._redis.set(key, value, ttl)
        except Exception as e:
            logger.warning(f"Redis set failed: {e}. Attempting reconnect...")
            if await self._try_reconnect():
                await self._redis.set(key, value, ttl)

    @property
    def connected(self) -> bool:
        return self._redis.connected


class AutoReconnectMT5:
    """Wraps titan.broker.engine.BrokerCompatibilityEngine with auto-reconnect."""

    def __init__(self, broker, policy: ReconnectPolicy | None = None,
                 on_event: Callable[[str, dict], Awaitable[None]] | None = None):
        self._broker = broker
        self._policy = policy or ReconnectPolicy()
        self._on_event = on_event
        self._reconnect_count = 0

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    async def _try_reconnect(self) -> bool:
        for attempt in range(self._policy.max_retries):
            try:
                if self._on_event:
                    await self._on_event("reconnect_attempt",
                                          {"component": "mt5", "attempt": attempt + 1})
                # Shutdown first if needed
                try:
                    self._broker.shutdown()
                except Exception:
                    pass
                ok = self._broker.initialize()
                if ok:
                    self._broker.detect_broker()
                    self._broker.resolve_symbol()
                    self._reconnect_count += 1
                    if self._on_event:
                        await self._on_event("reconnect_success",
                                              {"component": "mt5", "attempt": attempt + 1})
                    logger.info(f"MT5 reconnect succeeded on attempt {attempt + 1}")
                    return True
            except Exception as e:
                delay = self._policy.delay_for(attempt)
                logger.warning(f"MT5 reconnect attempt {attempt + 1} failed: {e}. "
                                f"Retrying in {delay:.2f}s")
                if self._on_event:
                    await self._on_event("reconnect_failed",
                                          {"component": "mt5", "attempt": attempt + 1,
                                           "error": str(e)[:100]})
                await asyncio.sleep(delay)
        return False

    async def ensure_connected(self) -> bool:
        """Check MT5 connection, reconnect if needed."""
        if not self._broker._mt5_initialized:
            return await self._try_reconnect()
        return True
